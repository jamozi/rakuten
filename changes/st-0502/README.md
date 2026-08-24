# ST-0502 — Item Search local implementation records

The current additive runtime is V2 and is documented in
`ITEM-SEARCH-RUNTIME-V2.md`. Its owner-private SQLite schema V2 uses exclusive
creation, exact schema and integrity recomputation, append-only durable rows,
hash-bound mutation history, device/inode and process-local monotonic pins,
exact commit recovery, and hostile provider/store boundary copies. It performs
zero live/provider actions. Cross-restart rollback detection has no external
anchor and is not claimed. Formal TST-014/TST-015, hosted CI, staging, release,
and Production remain `NOT_EXECUTED`.

## Predecessor V1 record

Classification: `MAXIMUM_SAFE_LOCAL_RECORDED_TEST_ONLY_ONE_PAGE_ITEM_SEARCH_SEAM`

This implementation-first slice is partial, non-authoritative, local-only, and
runtime-ineligible. It implements one deterministic `ITEM_SEARCH` exchange over
exact synthetic fixtures. It does not implement the full ST-0502 provider,
storage, retry, or pagination acceptance boundary.

## Closed implementation boundary

- Requests use API version `2026-07-01`, format version `2`, the canonical
  selector/sort/element vocabulary, exact integer and boolean types, and an
  explicitly sorted compact UTF-8 JSON fingerprint. Only the inert
  `CONTRACT_TEST` purpose and one requested page are accepted.
- The command binds one nonzero pre-resolved endpoint UUID, `ITEM_SEARCH`, the
  request fingerprint, and purpose without selecting an endpoint URL,
  credential, account, actor, real site, provider configuration, or job.
- The provider advertises only `RECORDED_TEST_ONLY`, `live_eligible: false`,
  and health `NOT_EXECUTED`. The application executes once, never sleeps,
  retries, checks live health, or follows another page.
- Exact raw UTF-8 JSON bytes are retained inside an immutable redacted response
  and bound to provider, API, request hash, SHA-256, UTC receipt time, HTTP
  status, request ID, and typed rate metadata. Duplicate keys, non-object JSON,
  non-finite numbers, malformed UTF-8, oversize input, and hash drift fail
  closed.
- The recorder compares the response against an immutable fixture and returns
  only a synthetic validation receipt. Its URI is `None`; storage and
  persistence are both `NOT_EXECUTED`. It does not retain another byte copy or
  access ST-0202.
- The canonical page and each item are hash-bound to the exact request and raw
  receipt. Provider item names, captions, URLs, affiliate URLs, review facts,
  and other text remain inert untrusted data. No value is treated as identity,
  approval, ranking, recommendation, review-body evidence, or a current catalog
  projection.
- Only `TRANSIENT` is classified retryable, but this slice performs zero
  retries. Every failure is sanitized, exposes no rejected value or raw body,
  and returns no partial result.

The ports expose provider capabilities, non-executed health, one execute,
normalize, classify, rate metadata, and one validation-only raw response
recording call. They expose no read/list/delete, repository, unit-of-work,
storage, persistence, filesystem, network, SDK, credential, or external-action
surface. The adapter uses no clock, randomness, environment lookup, mutable
history, or wildcard fixture.

## Authority and completion boundary

The field vocabulary is derived from the installed v0.4 Rakuten item-search
request, canonical-page, and artifact-reference schemas. ST-0202 and ST-0308
remain read-only dependencies. Because raw object persistence, provider calls,
runtime retries, and multi-page traversal are deliberately absent, Story
acceptance remains false and TST-014/TST-015 are not satisfied.

Formal tests, hosted CI, live/provider validation, object storage, persistence,
job/runtime integration, staging, release, and Production remain
`NOT_EXECUTED` and `NOT_AUTHORIZED`. Local pytest is development evidence only;
it is not `VALIDATED`, recoverability evidence, or release eligibility.

## Non-executable 2026-07-01 live-safe request policy v1

`python/raos/domain/catalog/rakuten_item_search_live_request_v1.py` adds a
separate pure request-policy projection for a later ST-0505 HTTPS adapter. It
does not change or convert the existing recorded request, command, service, or
fixtures, and it grants them no live eligibility.

- The projection accepts only API version `2026-07-01`, format version `2`,
  one requested page, and exact integer `hits` from 1 through 30. Retry and
  pagination-follow-up policy limits are fixed to zero; they are not execution
  observations.
- When both price bounds are present, `max_price_jpy` must be strictly greater
  than `min_price_jpy`; equal or inverted bounds fail closed.
- Its exact sorted element allowlist is the intersection of the installed v0.4
  vocabulary and the current official 2026-07-01 output table, minus
  `reviewCount`, `reviewAverage`, and `affiliateRate`. `tagIds` and
  `updateTimestamp` are absent because they are not in the current official
  output table; update-time sorting remains allowed. `affiliateUrl` remains
  permitted as a product-link output field.
- Its sort type contains only `standard`, item-price ascending/descending, and
  update-time ascending/descending. Review and affiliate-rate sorts cannot be
  represented.
- The normalized `has_review_only` constructor field is retained only as an
  exact-false guard for compatibility with the installed request vocabulary.
  It is omitted from the canonical projection, so no review or affiliate-rate
  filter field can reach the future provider-facing parameter surface.
- `attribute_flag=true` requires an exact nonzero `genre_id`, matching the
  current official input constraint; otherwise validation fails closed.
- Provider names, captions, URLs, and all other returned text remain
  `UNTRUSTED_DATA`; the projection exposes no provider-derived recommendation
  input. Legacy recorded review aggregates and affiliate rate may remain
  nullable inert facts, but this policy neither requests nor ranks by them.
- Values and validation failures are redacted and non-pickleable. The module
  contains no endpoint, account, credential, HTTP, network, environment,
  filesystem, storage, persistence, retry, pagination, or external-action
  implementation.

ST-0505 still owns any later adapter, wire mapping, account and credential
selection, live call, and TST-016 evidence. This ST-0502 policy is offline and
non-executable; it does not choose those values or authorize that work.

## Focused local check

```bash
.venv/bin/pytest -q -p no:cacheprovider tests/st0502
```
