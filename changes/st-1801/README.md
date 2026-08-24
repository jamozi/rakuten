# ST-1801 blocked local portfolio-expansion planner

This Story implements the maximum safe local boundary for the Canonical 30–45
article expansion. The exact ST-1705 predecessor is `NOT_ELIGIBLE`, and OD-001 has
not selected a real category. Consequently, the generated portfolio pack is always
`BLOCKED` and its 30 slots are explicit synthetic placeholders—not articles.

Every slot is fixed to `NOT_CREATED`, `NOT_APPROVED`, and `NOT_PUBLIC`. Article IDs,
slugs, URLs, schedules, quality scores, Claim counts, coverage, observations, and
evidence references remain absent or `UNAVAILABLE`. The tracked five-article
ST-1704 collection is hash-bound only as a non-attesting dependency; it is not
promoted into the expansion portfolio or treated as publication evidence.

## Recorded-synthetic evaluator

The fixed `RECORDED_SYNTHETIC_ONLY` fixture exercises the two ST-1801 acceptance
thresholds using exact decimal/integer arithmetic:

- aggregate quality score is at least 85; and
- evidenced major Claims equal all major Claims (100%).

Missing input and a zero Claim denominator produce `UNAVAILABLE`, never zero or a
pass. Out-of-range values, booleans, negative counts, and supported counts above the
denominator are rejected. Even a synthetic `PASS` is explicitly ineligible for
article approval, Pilot evidence, GATE evidence, publication, or Story acceptance.
It does not evaluate the additional per-axis floors and zero-tolerance checks needed
by the full quality gate.

Affiliate rate, EPC, RPM, reward, cost, and profit are absent from the planner and
evaluator inputs. They cannot influence category, slot selection, ordering, content,
or recommendation order.

## Owner generation

Run from the exact physical repository root with the already synchronized pinned
environment; generation performs no install, network, provider, credential, CMS, or
external action:

```bash
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1801_portfolio_expansion.py

/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1801_portfolio_expansion.py --check
```

The two generated outputs are published under one durable, recoverable transaction.
The next normal build rolls back an interrupted prepared transaction or finishes a
committed cleanup. `--check` is read-only and refuses pending recovery state. Fixed
inputs are read descriptor-relatively without following links, under a 2 MiB limit;
JSON/YAML duplicate keys and YAML aliases are rejected.

## Authority boundary

This implementation does not mutate the Status Registry, create or approve content,
accept formal evidence, call a provider, publish, stage, release, deploy, or write to
Production. Formal TST-020/TST-032, actual 30–45 article execution, human approval,
publication, live observation, staging, release, and Production remain
`NOT_EXECUTED`.
