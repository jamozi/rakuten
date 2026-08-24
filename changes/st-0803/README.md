# ST-0803 — additive local comparison validation runtime V2

V2 adds an executable, recorded-synthetic comparison validation boundary while
preserving the historical V1 pure validator for ST-0804 compatibility. Neither
runtime ranks products, produces recommendations, changes an Article, or grants
publication or Production authority.

## Exact input boundary

One V2 envelope binds the exact Article ID/version/body, approved Source Packet
Version/content, complete Claim set, versioned candidate universe, versioned
axis catalog, product-by-axis Fact set, evaluation time and complete comparison
input. Products bind separate subject and variant identity hashes. Decimal,
date, Boolean, code and text values are typed and serialized deterministically;
decimal values use an exact `NUMERIC(30,10)`-compatible representation.

Every product/axis coordinate is explicit. `VALID`, `UNKNOWN`, `MISSING`,
`CONFLICT`, and `UNSUPPORTED` are separate states. Unknown values remain
visible and cannot be imputed. Required missing values, conflicts, unsupported
values, identity/variant/unit mismatches, stale or future Facts, and finance or
affiliate axis aliases block. Missing, malformed, oversized, untrusted or
hash-incoherent input is `UNEVALUABLE`.

## ST-0605 receipt handshake

V2 consumes the exact precomputed ST-0605 Claim/Evidence snapshot. It calls the
ST-0605 public requirement function to validate the required `COMPARISON`
kind/subject/input tuples without requiring an earlier ST-0605 `PASS`. All
other required receipts, including exact ST-0504 identity receipts, must
already be present and valid. A finding-free result emits matching
recorded-synthetic ST-0803 receipts. The input is not mutated; a caller may
assemble a new ST-0605 snapshot with those receipts and rerun ST-0605.

The receipt decision digest is a deterministic corruption check, not owner
authentication. Live identity resolution remains outside this runtime.

## Runtime and authority boundary

- Pure evaluator: no I/O and no authority.
- Inward port: one read-only envelope lookup.
- Result seam: process-local metadata-only append; no update/delete surface.
- Adapter: generated fixture bytes only, ENV-DEV/CI only, reparsed and
  hash-checked on every read.
- Generator: exact locked toolchain and source hashes, bounded YAML/JSON,
  symlink/hardlink rejection, descriptor-relative
  `renameat2(RENAME_EXCHANGE)`/no-clobber publication, foreign-target
  restoration and multi-output rollback.
- Network, credential, provider, persistence, Article, recommendation,
  ranking and publication operations: forbidden.

A finding-free recorded fixture returns `LOCAL_VALIDATED`, while all
publication/recommendation/ranking/Production authority flags remain false.
Formal TST-007/TST-020, live validation, hosted CI, staging, release and
Production remain `NOT_EXECUTED`.
