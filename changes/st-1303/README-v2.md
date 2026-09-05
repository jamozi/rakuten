# ST-1303 V2 — recorded/synthetic attribution runtime

This additive V2 replaces the V1 reference-only limitation with a maximum-safe
local implementation. It executes only a tracked synthetic scenario in
`ENV-DEV`/`CI`; `OD-003` and the real Rakuten report mapping remain unresolved.

The domain implements four strictly separated concepts: immutable provider input,
Direct, Estimated and Unattributed. Direct requires a hashed synthetic provider
key and an exact five-slot article binding. Estimated attribution uses verified
same-program, same-period, mature affiliate-click weights. Integral JPY is split
with deterministic largest remainder and slot-number tie-breaking. Insufficient
or unsafe evidence remains Unattributed. Every allocation carries the method
version, complete input hash, confidence basis points and a closed reason.

The versioned measurement contract binds exactly five article slots to
`article_id`, slug, tracked packet SHA-256 and intent classification under the
fixed program `WORDPRESS_BLOG_RAKUTEN_AFFILIATE`. It accepts typed search,
article, affiliate, outcome, direct reward, work/cost, broken-link and cohort
observations. Missing, unverified, zero-denominator, immature, period-mismatched
or program-mismatched inputs produce `UNAVAILABLE`, never an invented zero.
Program-level unattributed reward is kept separate and cannot be allocated to an
article.

Generate or check the deterministic local projection:

```text
.venv/bin/python scripts/build_st1303_attribution_engine.py
.venv/bin/python scripts/build_st1303_attribution_engine.py --check
```

This command is the V2 executable-local owner. The older
`build_st1303_attribution_engine_reference_plan.py` remains a frozen,
non-executable historical reference and is not a V2 runtime dependency.

Normal generation first refreshes only the upstream source/packet hash fields
in the runtime YAML and their matching references in the recorded/synthetic
fixture. The existing five article IDs, slugs, slots and intent classifications
must remain unchanged. The old fixture must pass its complete input-hash and
synthetic-profile validation before any rebind. Measurement values, dates,
verification states, authority and canonical bindings are never rewritten.
The fixture contract/input hashes are then recomputed from the typed request;
this is synthetic test-data maintenance, not new measurement or live evidence.
Each changed file is replaced atomically; an ordinary write failure rolls back
prior binding replacements. An interrupted or inconsistent pair remains
fail-closed. `--check` and the runtime loader never refresh or write these
references: they continue to reject stale bindings and generated-output drift.

Confirmed/unattributed reward, commission, incremental cost, commission rate,
EPC, RPM, profit and every other finance value are excluded from improvement,
product-selection and recommendation-order inputs. ST-1303 emits no Learning
Report or improvement proposal; downstream learning may only produce a
human-reviewable proposal from non-finance evidence and may not mutate content.
The runtime has no HTML, CTA, product, order, snapshot, publication, network,
provider, credential, database or persistence capability. Formal TST-007 and
TST-030, real provider calibration, live, staging, release and Production remain
`NOT_EXECUTED`.
