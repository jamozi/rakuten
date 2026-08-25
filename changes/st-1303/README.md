# ST-1303 attribution-engine reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_ATTRIBUTION_ENGINE_REFERENCE_PLAN`.

This directory defines a deterministic, source-derived inventory of the
constraints and unavailable selections for a future attribution engine. It is
not an attribution algorithm, method implementation, run command, event
collector, fact model, repository, unit of work, transaction, job, event
emitter, audit, outbox, fake persistence layer, provider adapter, or executable
runtime.

The current ST-1202 dependency exposes six disabled public-event requirements
but no value-bearing events, identities, consent eligibility, collector, or
emission. The current ST-1302 dependency exposes a non-executable provider-fact
commit reference plan but no provider facts, amounts, periods, identities,
commit result, or persistence. OD-003 remains blocking and
`EXTERNAL_EVIDENCE_REQUIRED`.

Dependency provenance distinguishes each original feature commit from the
commit whose tree supplies the exact bound artifact bytes. ST-1202's seven
files remain byte-identical to its feature commit. ST-1302's nine current files
are bound at current mechanical artifact commit
`02b7441f216e0ed01b3e8c6808db4ab7ec19be8d`, while retaining its original
feature commit separately. The binding is provenance only and grants no runtime,
provider, publication, staging, release, or Production authority.

Canonical sources require Provider Fact, Direct, Estimated, and Unattributed
to remain distinct. Direct requires a verifiable provider key. Estimated
attribution is explicitly non-official and requires a method version, input
hash, confidence, and reason. Insufficient evidence remains Unattributed, and
allocated totals must conserve the provider total. Those constraints do not
select an executable method.

Every method, window, bucket, eligibility rule, weight, confidence rule,
conservation basis, tolerance, rounding rule, correction policy, run identity,
and persistence choice remains null or `NOT_EVALUATED`. Event, provider-fact,
candidate, allocation, run, emitted-event, and write collections remain empty.
Their counts and totals remain null—not zero—and no empty collection can
produce a vacuous pass.

The generated JSON and manifest are owned only by:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1303_attribution_engine_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1303_attribution_engine_reference_plan.py --check
```

Local generation and tests do not satisfy Story acceptance or formal
TST-007/TST-030. Runtime, database, provider, browser, live, staging, release,
and Production work remains `NOT_EXECUTED` and unauthorized.
