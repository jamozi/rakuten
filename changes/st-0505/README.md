# ST-0505 — Rakuten live-smoke reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_RAKUTEN_LIVE_SMOKE_REFERENCE_PLAN`

Contract revision `1.2.3` is partial, non-authoritative, local-only,
non-executable, and runtime-ineligible. It binds the committed ST-0502
recorded-only adapter boundary and preserves OD-015's blocking safe default:
`Recorded fixtureのみ`. It is a reviewable plan, not a live adapter, runnable
smoke command, provider observation, or formal result. A separate local-only
credential setup/check interface is now available, but it has no runtime reader
and is not connected to this live-smoke plan.

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
- No live provider/runtime adapter, SDK, network client, repository, unit of
  work, account, endpoint, request payload, runner, or executable smoke command
  is added or selected. The only new filesystem interface is the fixed ignored
  local store `.secrets/rakuten-live-smoke`; no runtime consumer is added.
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

## Local credential intake

The implementation-ready design is
`DESIGN_HANDOFF_V1_ST0505_RAKUTEN_LIVE_SMOKE_CREDENTIAL_INTAKE_V1.yaml`.
It records the connected owner directives as setup/check-only authority; it
does not claim an exact-hash owner statement or approval for credential values
or a provider call.

The fixed commands are:

```bash
/home/minami/rakuten/scripts/rakuten_live_smoke_credentials_python.sh setup
/home/minami/rakuten/scripts/rakuten_live_smoke_credentials_python.sh check
```

The launcher uses the pinned CPython with exact `-I -S` flags for both its
interpreter validation and the final credential CLI. Python `site` import and
executable `.pth` startup hooks are therefore disabled; the credential CLI has
a standard-library-only dependency surface.

`setup` accepts exactly the application ID and access key from `/dev/tty` with
terminal echo disabled and requires canonical terminal mode. Values are
bounded to 4094 bytes so Linux canonical input cannot silently truncate a
submitted value at its 4095-byte payload boundary. On a control byte or length
overflow, the mutable prefix is wiped immediately and the current line is
drained only through its first LF while ECHO/ECHONL remain disabled. The drain
switches its private descriptor to nonblocking mode and has a fixed 4096-byte
cap and one-second monotonic deadline; incomplete drain uses atomic `TCSAFLUSH`
input discard and terminal restoration and returns only the fixed sanitized
failure. Every outcome after hidden mode was applied—including valid input,
successful rejection drain, EOF, interrupt-equivalent, prompt/read error, and
failure—restores the terminal with `TCSAFLUSH`. Each prompt therefore requires
one fresh canonical line; queued typeahead or a multiline clipboard paste is
discarded before echo returns and can never become input to a later prompt or
the invoking shell. It never accepts values through argv, environment, stdin,
chat, or tracked files. It creates only
`rakuten_web_service_application_id` and
`rakuten_web_service_access_key`; the optional `rakuten_affiliate_id` is
excluded from V1. Existing exact metadata returns `READY` without prompting;
partial, unknown, linked, special, or unsafe state fails closed without
overwrite, automatic deletion, or repair. A failed normal write leaves its
owner-only residue fail closed because Linux has no inode-bound unlink for this
path-based store; the command never risks deleting a replacement entry.

Both aliases are written below the fixed non-ready
`.secrets/.rakuten-live-smoke.preparing` directory. Only a fully fsynced pair
is atomically promoted with Linux `renameat2(RENAME_NOREPLACE)`. A retained
`.rakuten-live-smoke.committing` directory becomes the metadata-only
`.rakuten-live-smoke.ready` marker after final-store inode verification. A
separately retained `.rakuten-live-smoke.validating` marker keeps every
post-READY verification or fsync failure `INVALID`; only after internal
metadata inspection passes is it promoted, as the last operation, to
`.rakuten-live-smoke.committed`. External `READY` requires the final store plus
both ready and committed markers, with no preparing, committing, or validating
marker. Thus a final-looking two-file directory alone is never READY.

`check` inspects names and filesystem metadata only. It never opens or reads an
alias file. `READY` means only that the exact owner-only `0700`/`0600` shape is
present; it does not establish credential validity, consent, account binding,
live-provider authority, or TST-016 evidence.

Setup and check are single-process maintenance commands. No uncoordinated
same-EUID process may mutate `.secrets/rakuten-live-smoke` or the five fixed
preparing, committing, ready, validating, and committed transaction names while
either command runs; such a mutator is outside this local trust boundary.

The current Item Search `2026-07-01` documentation requires an application ID
and access key and makes affiliate ID optional. Future access-key transport is
still restricted by RAOS to `DEDICATED_HTTP_HEADER_ONLY`; this slice adds no
transport or endpoint execution. No real credential setup/check or provider
call was executed while implementing this interface.

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
