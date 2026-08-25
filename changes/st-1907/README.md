# ST-1907 — disabled content portfolio optimizer boundary

Status: local implementation of the maximum-safe Post-MVP interface.
Canonical status remains `DEFERRED_POST_MVP`; formal TST-032 and the Story's
separate release decision remain `NOT_EXECUTED`.

`DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE` is exactly `DISABLED`. The only executable
scope is `RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY`, accepted only by the
application service in ENV-DEV or CI. Disabled evaluation fails before the
inward port is called. There is no live/activation/provider/persistence/release
state or interface.

The adapter consumes one exact caller-owned canonical JSON byte string once.
It accepts a closed schema containing non-personal, non-finance, preclassified
proposal signals only. It has no filesystem path, URL, provider SDK,
environment lookup, credential, network, database, publication, or mutation
capability. Unknown/duplicate fields, non-canonical bytes, float/NaN values,
source drift, replay, malformed values, finance-bearing signals, personal
data, requested recommendation/order changes, or requested publication
mutation fail closed with redacted failures.

An available evaluation requires an independently verified ST-1805 human
decision boundary, at least one observation, one fixed 14-day period, the
fixed affiliate program, exact measurement and signal-policy hashes, verified
inputs, mature cohorts, and an available positive denominator for every
signal. Any gate failure returns `UNAVAILABLE` and an empty proposal list; an
unavailable value never becomes zero.

Only the closed actions `STRENGTHEN`, `CONSOLIDATE`, and `WITHDRAW` may be
rendered, in deterministic action/article/signal order. They are immutable
`HUMAN_REVIEW_METADATA_ONLY` candidates. They are non-actionable, require
human review, carry no threshold selection or recommendation ranking meaning,
and have no apply or mutation method. The service never changes product
selection, recommendation order, article HTML, CTA, publication snapshots, or
public content. Reward, commission, affiliate rate, EPC, RPM, cost, and profit
are absent and structurally excluded from editorial recommendation/order.

The checked-in recorded fixture binds the current exact ST-1805 output. Since
that dependency is `BLOCKED/NO_DECISION`, unauthorized, has zero actual
observations, and is not locally integrated, owner generation deterministically
produces `UNAVAILABLE` with zero proposals.

Owner commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1907_content_portfolio_optimizer.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st1907_content_portfolio_optimizer.py --check
```

Only this owner writes
`changes/st-1907/generated/content-portfolio-optimizer-report.v1.json` and
`changes/st-1907/manifest.yaml`. These artifacts are local DEV/CI evidence,
not formal TST-032, real-observation, staging, release, Production, or Story
acceptance evidence.
