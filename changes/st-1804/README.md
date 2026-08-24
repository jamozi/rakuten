# ST-1804 recorded/synthetic GATE-3 economics

Classification:
`MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_RECORDED_SYNTHETIC_GATE3_NON_ATTESTING`.

This Story implements a deterministic local GATE-3 evaluator and immutable
pack. It is not an actual 30–45 article pilot, a real observation period,
formal TST-030/TST-032 evidence, a confirmed-profit claim, Gate approval, or
Scale/Hold/Pivot authority. The generated pack is always `BLOCKED`,
`actual_observations` is empty, and `gate_pass_claim` is false.

## Confirmed basis without false attribution

The synthetic vector keeps Provider, Direct, Estimated and Unattributed reward
separate. Provider total is a program total, never article attribution.
Direct-basis EPC, RPM, profit, payback, concentration and update-cost ratio
exclude Estimated and Unattributed reward. Unattributed reward is never
allocated to an article. Each month must conserve Provider = Direct + Estimated
+ Unattributed or every finance-dependent result becomes `UNAVAILABLE`.

The current dependency evidence cannot be promoted: ST-1803 is a 90-day
recorded synthetic GATE-2 vector, ST-1305 is a different 14-day recorded
synthetic finance vector with `PARTIAL` reconciliation, and OD-003 has no real
Rakuten report sample. OD-005 also leaves actual human labor cost `UNKNOWN`,
not zero. The generator records this period mismatch and external basis debt.

## Deterministic availability and thresholds

The strict input uses three contiguous calendar-month entries in an append-only
SHA-256 chain. Missing, unavailable, unverified, immature, mixed-period,
mixed-program, wrong-source, attribution-unverified, cost-unverified,
conservation-mismatched and zero/nonpositive-denominator inputs remain typed
`UNAVAILABLE`; none become a silent zero. Explicit synthetic zero is distinct.
Arithmetic uses `decimal.Decimal`, six places and `ROUND_HALF_EVEN`. The
fixture has program-level totals but no Canonical promising-article-group
binding, so content payback remains `UNAVAILABLE` instead of projecting the
program total onto the wrong grain. A non-positive three-month Profit II also
leaves the alternative reasonable-improvement-trend branch as human-judgment
`UNAVAILABLE`.

Every metric row points to a shared immutable evaluation context containing
the three exact periods, program, cohort maturity, recorded timestamp and
source-bundle hashes. Its freshness is explicitly non-live recorded/synthetic.

The harness calculates the numeric GATE-3 thresholds, but every computed
criterion is `INELIGIBLE_NON_ATTESTING`. EPC stability and forecast error
manageability remain `UNAVAILABLE` because Canonical requires judgment.

## Editorial and authority separation

Finance, reward, commission, affiliate rate, EPC, RPM, cost and profit cannot
rank products or change article HTML, CTA, product selection, recommendation
order, or publication snapshot. ST-1305 learning candidates are referenced as
read-only review candidates and remain based on its closed non-finance signal
allowlist. No mutation, provider/network call, credential lookup, persistence,
public projection, publication, Gate approval, status apply, staging, release,
or Production capability exists.

## Generate and verify

```text
/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1804_gate3_economics.py
/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1804_gate3_economics.py --check
```

The owner atomically replaces only
`changes/st-1804/generated/gate3-economics.local-blocked.v1.json`. Local checks
do not constitute Canonical `VALIDATED`, staging, release or Production status;
all formal/live work remains explicitly `NOT_EXECUTED`.
