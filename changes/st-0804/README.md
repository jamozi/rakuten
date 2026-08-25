# ST-0804 — deterministic recommendation engine V2

Local status: `LOCAL_IMPLEMENTATION_COMPLETE`.

ST-0804 now has an additive, locally executable V2 runtime downstream of the
integrated ST-0803 V2 comparison validator. The historical pure V1 module is
kept byte-compatible for existing consumers; it is not silently promoted into
the new receipt boundary.

## Exact input boundary

The V2 envelope binds all of the following as one immutable recommendation
input:

- exact article ID/version/body, approved Packet version/content and complete
  Claim-set hashes projected by ST-0803;
- exact candidate-universe, axis-catalog, Fact-set and temporal-scope hashes;
- the independently recomputed ST-0803 request/report bytes and a matching
  process-local record receipt;
- a versioned decision context and its article binding;
- the canonical `RAOS-CONTENT-RECO-001@1.0.0` source hash and every named rule;
- every axis definition, Decimal weight, normalization basis, product/axis
  Fact binding, normalization input/decision hash and evidence state.

The runtime reruns ST-0803 and compares canonical report bytes. A structural,
untrusted or missing input is `UNEVALUABLE`; a trusted semantic mismatch is
`BLOCK`; a finding-free input is `LOCAL_CALCULATED`. No prior ST-0605 PASS is
required: ST-0803's own exact COMPARISON attestation tuple remains inside the
bound report and the separate record receipt can only refer to that report.

## Deterministic calculation

Only validated specifications, explicit use conditions, or their intersection
may provide pre-resolved finite Decimal scores in `[0, 1]`. ST-0804 does not
invent a category normalization algorithm. Unknown, missing, conflicting or
unsupported cells retain an explicit state and no score; they are never
converted to zero, average, pass or a winner.

Hard constraints run before scoring. Coverage, base score, uncertainty penalty
and clamped final score follow the pinned methodology. Internal projection is
four-decimal `ROUND_HALF_EVEN`; the public projection is an integer only in the
local explanation. Ranking begins at 0.80 coverage and primary eligibility at
0.90. Penalties cap at 20. A score difference at or below 2.0 creates a
co-recommendation group whose members use stable product-ID order; 2.01 starts
a new group. Collection permutations produce byte-identical reports and
explanations.

## Editorial/finance separation

Affiliate, commission, reward, rate, EPC, RPM, finance, revenue, profit and
sponsorship aliases cannot be model fields. The recorded adapter recursively
checks every key and string value before structural resolution, including
nested maps/lists, camel case, NFKC/fullwidth forms, Japanese terms and common
leet variants. This detector is also applied at the domain context/axis
boundary. Validated specification/use-condition bindings are the only values
that can affect order.

There is no override, approval, persistence, provider, mutation, public
ranking, activation, publication or external-write surface. The only appender
stores process-local report digest/canonical-byte metadata and re-resolves the
fixture before every append. All authority flags remain false.

## Generated owner artifacts

`recommendation-runtime.v2.yaml` owns the recorded seed. Run:

```bash
.venv/bin/python scripts/build_st0804_recommendation_runtime.py
.venv/bin/python scripts/build_st0804_recommendation_runtime.py --check
```

The owner publishes the fixture and runtime manifest together through the
hash-bound `secure_generated_publication.py` helper. Existing targets use
descriptor-relative `renameat2(RENAME_EXCHANGE)` with displaced/reverse
identity verification; missing targets use a no-clobber hard link. Symlinks,
hardlinks, parent/target swaps, foreign material, partial failures and
`BaseException` interruption fail closed with foreign-preserving rollback.
`--check` performs no write transaction.

## Verification boundary

The focused V2 suite covers exact upstream/request/report/receipt bindings,
Decimal/property determinism, 0.79/0.80/0.90 thresholds, explicit unavailable
evidence, hard failures, penalty/cap/clamp and 2.0/2.01 ties, hostile aliases,
all bounds, adapter re-resolution, generator tamper/TOCTOU/rollback and
manifest identity. Historical ST-0804 and integrated ST-0803 suites remain
regressions.

This is local implementation evidence only. Canonical registry changes,
formal TST-007/TST-020, hosted CI, live validation, staging, release,
publication and Production remain `NOT_EXECUTED`.
