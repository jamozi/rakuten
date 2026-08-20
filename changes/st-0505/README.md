# ST-0505 — Rakuten live-smoke reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_RAKUTEN_LIVE_SMOKE_REFERENCE_PLAN`

Contract revision `1.1.0` is partial, non-authoritative, local-only,
non-executable, and runtime-ineligible. It binds the committed ST-0502
recorded-only adapter boundary and preserves OD-015's blocking safe default:
`Recorded fixtureのみ`. It is a reviewable plan, not a live adapter, runnable
smoke command, provider observation, credential interface, or formal result.

## Closed reference boundary

- The plan binds ST-0502 commit
  `3b63ea8b35b25f1c38c53a7fb5e8c0b596ddd0ab` and an exact ordered inventory of
  eleven committed owner artifacts by SHA-256: the existing nine recorded
  contract artifacts followed by the live-safe request-policy module and its
  dedicated hostile test.
- ST-0502 supports only deterministic, one-page `ITEM_SEARCH` for
  `CONTRACT_TEST` using `RECORDED_TEST_ONLY`. It is not live eligible; provider
  health, storage, and persistence remain `NOT_EXECUTED`; its validation
  receipt has no URI; it retries and paginates zero times.
- The separately bound `RakutenItemSearchLiveRequestV1` policy is pure and
  non-executable. Its provider API version is `2026-07-01`, page is exactly one,
  hits are bounded from 1 through 30, retry and pagination-follow-up limits are
  zero, review-derived and affiliate-rate request inputs are excluded, and
  provider text is `UNTRUSTED_DATA`. This binding does not make the recorded
  provider live eligible or make the policy executable.
- No live provider/runtime adapter, SDK, network client, filesystem path,
  repository, unit of work, account, endpoint, environment, credential,
  secret name, token, request payload, runner, or executable smoke command is
  added or selected.
- No auth, schema, rate, quota, capacity, cost, latency, response, provider
  request ID, timestamp, or success/failure observation is fabricated. Empty
  observations mean no execution evidence, not zero errors or successful auth.
- Activation is disabled. Provider, network, credential, staging, release,
  Production, storage, persistence, and external actions are forbidden or
  `NOT_EXECUTED`; every action count is an exact integer zero.

The generated JSON is produced only by the strict fixed-path owner builder. It
contains plan and boundary metadata only. It cannot read process environment,
resolve credentials, contact Rakuten, construct a live request, execute a
smoke, retry, paginate, write a report externally, or persist provider data.

## Completion boundary

OD-015 remains `EXTERNAL_EVIDENCE_REQUIRED` and blocking. Story acceptance is
false, canonical implementation remains `NOT_STARTED`, and verification
remains `NOT_EXECUTED`. Local generation and pytest do not satisfy TST-016 or
establish live auth/schema/rate behavior, hosted CI, staging, release, or
Production eligibility.

## Owner generation

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0505_rakuten_live_smoke_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0505_rakuten_live_smoke_reference_plan.py --check
```
