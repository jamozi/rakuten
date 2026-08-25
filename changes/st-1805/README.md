# ST-1805 recorded/synthetic portfolio decision boundary

Classification:
`MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_RECORDED_SYNTHETIC_NO_DECISION`.

This Story implements a deterministic, immutable local evaluation of the
quality, economics and risk evidence required before a Product Owner can make
a Scale/Hold/Pivot decision. It deliberately returns `BLOCKED` and
`NO_DECISION`. It cannot approve GATE-3, choose or authorize Scale/Hold/Pivot,
change an article/category limit, or mutate any editorial/publication state.

The bound ST-1804 pack is recorded/synthetic, has no actual observations,
claims no Gate pass and grants no scale authority. Therefore quality,
economics, risk, formal TST-032 and Product Owner decision evidence all remain
ineligible. Synthetic threshold calculations are never promoted to actual
business evidence. Missing or unverified evidence is not converted to zero.

Finance, reward, affiliate rate, EPC, RPM and profit cannot affect product
selection or recommendation order. The implementation consumes no financial
amounts; it only preserves the dependency's non-attesting evidence state.

Generate and verify:

```text
/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1805_portfolio_decision.py
/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1805_portfolio_decision.py --check
```

The owner writes only
`changes/st-1805/generated/portfolio-decision.local-blocked.v1.json`.
Local tests are not formal TST-032, a Human Gate decision, staging, release,
Production readiness or evidence of real profitability.
