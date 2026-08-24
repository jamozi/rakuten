# ST-1803 recorded-only GATE-2 observation

Classification:
`MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_RECORDED_SYNTHETIC_GATE2_NON_ATTESTING`.

ST-1803 now has a deterministic process-local domain, inward port, strict
caller-bytes recorded adapter, application job, versioned contract, append-only
hash-chained five-slot fixture, and a single-output owner generator. The result
is an immutable improvement report embedded in a GATE-2 pack whose overall
state is `BLOCKED`. It is not an actual pilot observation, formal TST-030 or
TST-032 evidence, Gate approval, or permission to scale.

## Observation and arithmetic boundary

The fixture binds exactly five article slots to article ID, slug, packet hash,
one 90-day period, and the fixed program
`WORDPRESS_BLOG_RAKUTEN_AFFILIATE`. Each normalized article entry is chained to
the preceding SHA-256 and the program-level entry closes the chain. Runtime
objects are frozen, non-pickleable, and redacted. The adapter consumes one
exact byte sequence once; duplicate keys, unknown fields, floats, non-finite or
negative values, malformed zero states, chain drift, hash drift, replay, and
oversized inputs fail closed.

The typed input accepts search impressions/clicks, qualified organic sessions,
article views, affiliate clicks, pending/confirmed/rejected outcomes, direct
confirmed reward, work minutes, incremental cost, broken links/link checks,
index/query/freshness/complaint facts, and a separate program-level
unattributed reward. All results use exact integer aggregation and
`decimal.Decimal` with six places and `ROUND_HALF_EVEN`.

Missing, unavailable, unverified, mixed-period, mixed-program, wrong-source,
immature-cohort, attribution-unverified, missing-slot, zero-denominator, and
reward-conservation failures remain typed `UNAVAILABLE`; none become a silent zero.
An explicit observed zero stays a real zero. Direct reward plus unattributed
reward must conserve to the provider total. Unattributed reward is never allocated
to an article.

## Learning and editorial separation

The local report calculates search CTR, affiliate click rate, confirmed reward
per click, confirmation rate, and confirmed reward per content hour alongside
the GATE-2 search/freshness rates. Only search, behavior, and freshness facts
may select deterministic improvement candidates. Reward, cost, affiliate rate,
EPC, RPM, and profit cannot select or order candidates and never enter article
recommendation logic.

Candidates are output-only records with authority `NONE`. The implementation
cannot change article HTML, CTA text or placement, product selection,
recommendation order, publication snapshot, tracked measurement inputs, or any
external system. No publication, tracking, provider/network request, staging,
release, or Production capability exists in this slice.

## GATE-2 truth boundary

The generated harness deliberately uses recorded synthetic numbers to exercise
threshold boundaries. Every numeric GATE criterion is therefore
`INELIGIBLE_NON_ATTESTING`; qualitative and human judgments remain
`UNAVAILABLE`; formal/live items remain `NOT_EXECUTED`; and the blocked ST-1802
predecessor remains visible. `actual_observations` is empty and
`gate_pass_claim` is false.

OD-004, OD-007, OD-012, and OD-015 remain unresolved. The safe defaults are a
recorded fixture, no live rank/keyword provider, no category-specific freshness
claim, tracking disabled, and no credential use. The implementation does not
read the owner-private ST-1704 ledger or claim an actual 30–45 article pilot.

## Generate and verify

```text
/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1803_gate2_observation.py

/home/minami/rakuten/.venv/bin/python -I -B \
  scripts/build_st1803_gate2_observation.py --check
```

The generator owns only
`generated/gate2-observation.local-blocked.v1.json`. It validates the exact
Canonical and dependency bindings, regenerates the report through the runtime,
and atomically replaces one target after durable sibling staging. A stale stage
is recoverable because the old target remains intact until the single rename.

Formal TST-030/TST-032, actual observation-period sufficiency, real Search
Console/access/provider data, consent/privacy activation, human Gate review,
staging, release, deployment, and Production remain explicitly `NOT_EXECUTED`.
Local checks do not constitute Canonical `VALIDATED` status.
