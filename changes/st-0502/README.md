# ST-0502 — recorded-only one-page Rakuten item search

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

## Focused local check

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  pytest -q tests/st0502
```
