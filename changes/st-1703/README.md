# ST-1703 market-learning pilot Wave 1

> 2026-08-22 self-hosted owner-local slice: the separate, reversible
> `SELF_HOSTED_MINIMUM_START_V1` contract for `https://kurashinoshirube.com`
> lives under `changes/st-1703/self-hosted-minimum-start-v1/`. Its local design
> record does not rewrite the historical exact-hash handoffs below, resolve the
> Canonical Open Decision registry, complete ST-1703, or authorize live write,
> theme activation, publication, formal TST, staging, release, or Production.

This change implements only the repository-owner-approved local slice bound by
`DESIGN_HANDOFF_V1_MARKET_LEARNING_PILOT_WAVE_1.yaml`. It does not complete the
canonical end-to-end ST-1703 Story.

The approved handoff SHA-256 is
`a8a94f4e70b082fdacb8672e7d3118b4178b0d312b935715b4613b87f52d0238`.
`MARKET_LEARNING_PILOT_WAVE_1` is the handoff's slice identifier; it is not a
claim that the repository implementation-first macro Wave 1 includes ST-1703.

## Preflight

- Story: `ST-1703`, slice `MARKET_LEARNING_PILOT_WAVE_1`.
- Objective: compose one eligible local ST-0805 result, one recorded-only
  ST-0502 result, and one draft-only WordPress port.
- Read: the exact approved handoff, canonical integration design/decisions/open
  decisions, ST-1703 backlog entry, TST-021/TST-022/TST-032 catalog entries,
  security controls, and the bound ST-0502/ST-0805 implementations.
- Open decisions: none inside this local slice. Canonical Open Decisions remain
  unresolved and no publication or production gate is advanced.
- Planned implementation: immutable pilot/domain values; one inward draft-only
  port; one local application service; one immutable recorded adapter; one
  transport-neutral no-I/O REST request builder; isolated tests.
- Migrations/contracts: none.
- Out of scope: network/browser/provider calls, authentication, credentials,
  real drafts, publish/schedule/delete/media, spend, live Rakuten, staging,
  release, revenue, formal TST, and production.

## Implemented boundary

The implementation preserves `domain <- application <- adapters/framework`:

- `raos.domain.editorial.market_learning_pilot` owns exact frozen values for
  the approved 90-day JPY pilot economics, draft create/update intent, stable
  content and operation bindings, immutable draft receipt, and immutable local
  evidence.
- `raos.ports.wordpress_draft.WordPressDraftPort` has one method, `apply`. No
  publish, schedule, delete, media, authentication, network, or generic HTTP
  capability is part of the inward port.
- `raos.application.editorial.market_learning_pilot.MarketLearningPilotService`
  accepts only `ENV-DEV` or `ENV-CI`, one already evaluated exact
  `PolicyEvaluationResult`, one exact recorded-only `RakutenItemSearchResult`,
  and the draft-only port.
- `raos.adapters.recorded_wordpress_draft.RecordedWordPressDraftAdapter` is an
  in-memory deterministic adapter. It creates one logical local draft, returns
  a replay receipt for an exact repeat, refuses changed-content create, and
  updates only through an explicit `UPDATE_DRAFT` bound to the current draft
  ID. It reads no environment, file, clock, database, browser, socket, or
  provider.
- `raos.adapters.wordpress_rest.OfficialWordPressRestRequestBuilder` is a pure
  transport-neutral value builder and response-shape validator. It performs no
  I/O and contains no HTTP client.

### Stable bindings

The content binding includes exactly:

- the fixed pilot configuration;
- article version ID;
- title and content;
- ST-0805 local result digest;
- ST-0502 request fingerprint (`page.request_sha256`); and
- ST-0502 raw-response digest (`page.raw_artifact.sha256`).

The operation binding additionally includes `CREATE_DRAFT` or `UPDATE_DRAFT`
and the existing draft ID. It is the local idempotency key. Exact create or
update repeats do not create a second logical draft or a second applied
operation. Automatic retry/resubmission is not implemented.

The pilot economics values are exact: 90 days, JPY, 30,000 JPY monthly
external-spend cap, 90,000 JPY cumulative-loss cap, 3,000 JPY labor cost per
hour, and `spending_activation=DISABLED`. These local values do not resolve
canonical OD-005 or OD-009 and do not authorize spend.

### ST-0805 and ST-0502 receiving boundary

`PolicyEvaluationResult` is accepted only when its exact local profile,
canonical JSON bytes, recomputed SHA-256, article binding, empty findings and
waivers, score and every eligibility input, authority booleans, and all five
`NOT_EXECUTED` states agree. Local eligibility never becomes publication or
production authority.

`RakutenItemSearchResult` remains `RAKUTEN_ICHIBA`, API `2026-07-01`, page 1,
`RECORDED_TEST_ONLY`, no storage/persistence, no live eligibility, no artifact
URI, and exact page/result rate binding. The slice does not inspect or use
product review bodies and introduces no provider path.

### Official WordPress REST request value

The builder requires one exact lower-case HTTPS origin with no path, userinfo,
query, fragment, encoding ambiguity, or malformed host. It emits only:

| Operation | Logical WordPress route | Exact transport path | Method | Expected response |
| --- | --- | --- | --- | --- |
| Create | `/wp/v2/posts` | `/wp-json/wp/v2/posts` | `POST` | `201` |
| Update | `/wp/v2/posts/<positive-id>` | `/wp-json/wp/v2/posts/<positive-id>` | `POST` | `200` |

The compact JSON object contains exactly `title`, `content`, and
`status="draft"`. The only header is `Content-Type: application/json`.
Authentication material is absent; the request carries only a bounded
lower-snake-case secret alias. An update also requires an immutable existing
draft receipt for the same positive draft ID. The response validator accepts
only the builder's exact origin/status pairing and returns only positive draft
ID, `draft`, and the HTTP status. Raw response content is not retained.

The official WordPress and Rakuten links and retrieval date are recorded in
the owner-approved handoff. This implementation made no network request and
does not claim separate live specification validation.

### Closed failures

Trust-boundary failures expose only one closed code, including
`POLICY_INELIGIBLE`, `POLICY_RESULT_INVALID`, `RAKUTEN_RESULT_INVALID`,
`DRAFT_UPDATE_REQUIRED`, `DRAFT_TARGET_MISMATCH`,
`DRAFT_EXCHANGE_UNAVAILABLE`, `WORDPRESS_ORIGIN_INVALID`,
`WORDPRESS_REQUEST_INVALID`, `WORDPRESS_RESPONSE_INVALID`, and
`OUTCOME_MISMATCH`. Caller content, provider content, URLs, response bodies,
and secret-like input are not interpolated into exceptions or representations.

## Local verification

Run Story suites in separate processes:

```bash
.venv/bin/python -m pytest tests/st1703 -q
.venv/bin/python -m pytest tests/st0502 -q
.venv/bin/python -m pytest tests/st0805 -q
```

Static and repository checks are recorded in `docs/worklogs/ST-1703.md` after
execution. A local pytest pass is local implementation evidence only; it is not
TST-021, TST-022, TST-032, staging, live, publication, release, revenue, or
production evidence.

## Remaining human and external gates

A real WordPress draft requires separate authorization, verified endpoint
ownership, and configured secret aliases. Publication remains a distinct human
approval after reviewing a real draft. Spend and live provider activation also
require separate approval. This slice exposes no publish, schedule, delete,
media-upload, or live-provider operation.

The canonical ST-1703 dependencies `ST-1702`, `ST-0906`, `ST-1007`,
`ST-1302`, and `ST-1505` and formal suites TST-021, TST-022, and TST-032 remain
unexecuted. No canonical status, generated status artifact, imported artifact,
or production-readiness record is changed by this slice.

## WordPress.com review-draft Wave 2 (approved implementation scope)

The repository owner separately approved the exact
`WORDPRESSCOM_REVIEW_DRAFT_WAVE_2` handoff at SHA-256
`798e005faee6c7367496a79e71b9a2d84fc9d9433e4e368276633a8539325cbd`.
The immutable approval binding is
`DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-REVIEW-DRAFT-WAVE-2-v1.yaml`.

This slice is a separate create-only review-copy path. It must not widen or
relabel the Wave 1 `WordPressDraftPort`, `WordPressDraftReceipt`,
`MarketLearningPilotService`, or `PilotEvidenceRecord`. Its only external
target is `https://kurashierabinote.wordpress.com`, its only post state is
`draft`, and publication remains unauthorized. Source Packet approval,
editorial policy approval, formal TST, staging, release, revenue, and
production status are not granted by a review copy.

The historical Wave 2 read-only activation preflight returned HTTP 404 for its
then-approved direct `/wp-json/` and `/wp-json/wp/v2/posts` paths while the
Coming Soon site was active. No POST was attempted. Wave 2A then selected a
fixed numeric-site `wp/v2` proxy route, whose authenticated edit-context
preflight later returned HTTP 403 before INTENT and before POST. The separately
approved Wave 2B activation below supersedes only that unavailable transport
with fixed WordPress.com REST v1.1 paths. Direct-site and `wp/v2` routes are now
historical and forbidden as fallbacks.

### Separate immutable implementation

Wave 2 adds new `WordPressComReviewDraft` and
`WordPressComReviewDraftReceipt` values plus a separate durable create-or-
replay inward port. A different outward port exposes only authenticated
fixed v1.1 capability preflight plus one create attempt; the raw HTTPS
adapter does not implement the application-facing port. Candidate construction
and both durable and HTTPS trust boundaries recompute the rendered-content and
operation hashes, pin the exact approved title, target, numeric-site v1.1 API path,
`CREATE_REVIEW_DRAFT` operation, `draft` status, and approved handoff hash, and
keep publication and production authority false. The committed Wave 1 local-
only types and service are not widened or relabeled.

The candidate builder rereads and verifies the exact byte lengths and SHA-256
values of the Wave 2 base handoff, Wave 2A route amendment, Wave 2B activation,
article proposal, and Source Packet candidate.
It extracts only the approved article region and renders a closed Markdown
subset. Input is escaped before rendering; output is limited to the approved
HTML tags and the `href` attribute on exact pinned lower-case HTTPS links.
Raw HTML, unsupported syntax, generated links, affiliate parameters, and
unbound source bytes fail closed.

### OAuth, transport, and durable one-create boundary

OAuth setup uses only the Authorization Code flow, exact `posts` scope, exact
blog, and exact IPv4 loopback redirect
`http://127.0.0.1:18703/oauth/wordpresscom/callback`. State is 32 random bytes
kept in memory and compared in constant time; the authorization code is also
memory-only. The user performs visible WordPress.com login and consent. The
implementation does not request a WordPress.com password and exposes no
password, implicit, PKCE, global, media, publish, update, or generic OAuth
mode.

The fixed secret root is `.secrets/wordpresscom-review-draft` with owner-only
mode `0700`; the client ID, client secret, and access-token aliases are regular
owner-only mode-`0600` files with no symlinked ancestor. If both client files
are absent, `oauth-setup` prints no credential value and reads each value only
from a controlling `/dev/tty` with echo disabled. Files are created
exclusively and fsynced; a partial pair, unsafe file, unavailable TTY, or
overwrite attempt fails closed. The sanitized refusal points the owner to
`https://developer.wordpress.com/apps/new/` and the exact redirect, target,
and scope, never to a credential value.

The official adapter uses system-verified TLS and one `POST` to
`https://public-api.wordpress.com/rest/v1.1/sites/256699520/posts/new`. Its
deterministic UTF-8 form body has exactly ordered `title`, `content`,
`status=draft`, and `publicize=false` members. It inherits no proxy,
follows no redirect, retries zero times, and has no direct, query-route,
domain-identifier, or legacy fallback. A
durable owner-only journal fsyncs `INTENT` before the sole POST and commits only
a strictly validated immutable receipt. An exact committed repeat returns the
recorded draft ID without network access. A pending, ambiguous, tampered, or
mismatched record stops without a second POST.

On the no-state branch and while holding the journal lock, the durable adapter
first performs one authenticated read-only
`GET /rest/v1.1/sites/256699520/posts?context=edit&number=1&fields=ID` against
the same fixed public API origin. The fixed query proves that the bearer can
access the exact numeric-site posts route in edit context while accepting only
the bounded exact `found`/`meta`/`posts` envelope and at most one positive
integer `ID`; an empty posts list is valid for a new site.
A 401/403/404, redirect,
malformed or widened response, or inaccessible edit context stops before any
state file or durable `INTENT` is written and before any POST; it never causes
a direct, query-route, domain-name, or legacy fallback. An exact `COMMITTED` replay and
every pre-existing `INTENT` are classified before preflight, so they perform no
secret read or network request; a residual `INTENT` is ambiguous.

### Exact operational commands

The only command surface is:

```bash
make wordpresscom-oauth-setup
make wordpresscom-create-review-draft
```

The Make targets invoke the pinned isolated CPython 3.14.6 launcher, which
clears inherited Python and WordPress credential environment variables and
uses restrictive process umask `0077`. It also fixes `PATH`, resolves reviewed
utilities by absolute path, clears `BROWSER`, and clears ambient
`SSL_CERT_FILE`, `SSL_CERT_DIR`, and `SSLKEYLOGFILE` controls. The production
TLS boundaries independently refuse those TLS variables before reading a
secret. The underlying CLI accepts only the exact `oauth-setup` and
`create-review-draft` subcommands with abbreviation disabled. There are no
target, endpoint, scope, status, retry, publish, schedule, update, delete,
media, taxonomy, sharing, publicize, or affiliate arguments.

`create-review-draft` verifies the five fixed source files before opening the
secret store, rebuilds the immutable candidate, and composes the outward HTTPS
attempt adapter inside the durable application adapter. The fixed access-token
alias and exact numeric-site capability must validate before a state file or
`INTENT` is written. Success or replay prints only canonical sanitized JSON
receipt fields, including the positive draft ID, exact `draft` status, content
and operation hashes, disposition, and explicit
`publication_authorized=false` and `production_eligible=false` boundaries.
The provider body is never retained; only its SHA-256 is committed after HTTP
200, positive `ID`, exact `site_ID=256699520`, exact `draft`/`post`, one safe
target-host HTTPS `URL`, and absent or exact-empty `publicize_URLs` validate.

In WSL, `oauth-setup` opens the exact authorization URL through the fixed
physical Windows PowerShell executable. The URL, including memory-only state,
is sent only on the child process's standard input, never in its arguments;
stdout and stderr are discarded, the command/environment are closed, and a
nonzero or timed-out launch fails closed. The inherited WSL interop endpoint
must be the canonical physical root-owned Unix socket
`/run/WSL/<positive-decimal>_interop` beneath physical root-owned non-writable
ancestors. The URL is also reconstructed byte-for-byte from the exact ordered
query contract before process launch.

The loopback listener ignores only up to three zero-byte TCP preconnections
inside the original fixed 300-second deadline. Any complete callback is
handled exactly once. It receives HTTP 200 only after method, Host, local bind,
path, query uniqueness, provider-error absence, code shape, and constant-time
state validation all pass; otherwise it receives HTTP 400 and is not retried.
A callback failure may print one closed `OAUTH_CALLBACK_*` diagnostic category
beside the unchanged generic reason. The category contains no observed URL,
query, state, code, header, peer, provider text, or credential value and is not
persisted.

A token-exchange failure may likewise print one closed `OAUTH_TOKEN_*`
diagnostic category beside the unchanged generic token-exchange reason. The
categories distinguish TLS environment/context, request setup, failure before
the request, an ambiguous request attempt, HTTP/content/body and strict JSON
validation stages, the three value-free provider-error classes
`invalid_client`, `invalid_grant`, and other, and each required response-field
boundary. Neither HTTP status, response body, provider description, token,
client credential, authorization code, nor any observed value is rendered or
persisted. Non-200 bodies are interpreted only when they satisfy the same
bounded content-type, UTF-8, duplicate-key, non-finite-value, depth, and node
checks as successful responses. This diagnostic surface does not relax token
acceptance: the WordPress.com documented lower-case `bearer`, positive
`blog_id`, and absent-or-exact `posts` scope remain required. The response-only
`blog_url` metadata may be exactly the approved host with lower-case `https`
or WordPress.com's lower-case `http` legacy metadata form, each with either no
path or one trailing slash. These are four byte-exact literals, not general URL
canonicalization. Every other URL form fails closed. URL diagnostics
distinguish type/parse, scheme, host, userinfo/port authority, path, and
query/fragment without rendering the observed URL. The metadata never selects
a transport: token exchange, API preflight, draft creation, and the validated
receipt continue to use only their fixed HTTPS hosts and the exact canonical
HTTPS target origin without a trailing slash.

### Offline, live, and formal status

Renderer, journal, HTTPS, OAuth, and command behavior have focused fake-only
local test evidence. Those tests do not open a browser, listener, external
socket, or live provider connection. Earlier owner-controlled OAuth attempts
were stopped while closed diagnostics were added; the owner later completed
OAuth setup successfully, and the approved Wave 2A handoff records an
owner-private token for the exact single-blog `posts` scope. The implementation
worker did not read or mutate it. The historical direct-endpoint 404 and
numeric-site `wp/v2` HTTP 403 are no longer selected routes. The approved v1.1
GET had bounded owner evidence of HTTP 200. A later owner-controlled execution
performed the sole v1.1 POST and then stopped as `CREATE_AMBIGUOUS`: the provider
encoded the exact site ID as decimal string `"256699520"`, while the first
validator admitted only its integer representation. The durable Wave 2B
`INTENT` therefore remains and no retry is authorized.

Read-only owner reconciliation identified one unique created draft, ID `7`, and
confirmed the exact immutable title and content, `status=draft`, `type=post`,
the canonical target-host URL, and `publicize_URLs=[]`. That observation does
not make the journal `COMMITTED`, authorize a second POST, or create a
reconciliation/migration path.

Even after one live non-public draft is created, it remains only an
owner-authorized editorial review copy. Formal TST-021/TST-022/TST-032,
canonical ST-1703 completion, Source Packet approval, editorial approval,
staging, publication, release, production, and revenue evidence remain
separate and unexecuted or unauthorized.

## WordPress.com review-draft Wave 2A numeric-site activation

The repository owner approved the byte-exact route amendment
`DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml`
at SHA-256
`5e69433222435305f8a2decef8840de4764565929d483f0e4d8b35fcd6ed7bf6`.
The detached approval overlay records the exact owner statement and the
evidence-bounded interpretation of its `HA-256` label as an evident `SHA-256`
prefix typo; the 64-hex digest, exact slice ID, approval verb, and independently
reverified file digest were unambiguous. The approved amendment bytes remain
unchanged.

Wave 2A replaces only the unavailable direct-site API authority and paths. The
one-attempt adapter can now open only system-verified HTTPS to
`public-api.wordpress.com:443`. A new operation uses exactly:

- `GET /wp/v2/sites/256699520/posts?context=edit&per_page=1&_fields=id`
- `POST /wp/v2/sites/256699520/posts`

There is no direct-site, query-route, domain-identifier, REST v1, discovery, or
browser fallback. The numeric site ID is not accepted from CLI, environment,
token metadata, or a provider response. The earlier direct-route 404 remains
historical activation evidence, but that route is no longer selected by the
approved implementation.

The candidate still requires the exact Wave 2 base handoff, article, Source
Packet, title, and rendered content. It additionally requires the exact Wave
2A amendment bytes. Its route-and-authority-bound operation SHA-256 is now
`2a29e77b52207d67c6be5017564d113657880b2f67a9e74d38d47e7538ff3e23`.
This changes neither article content nor editorial authority. The canonical
receipt target remains `https://kurashierabinote.wordpress.com`, status remains
exactly `draft`, and publication and production eligibility remain false.

Committed replay is checked before secret read, preflight, DNS, socket, or
network. With no state, the durable adapter holds its exclusive lock, performs
the authenticated numeric-site GET, writes and fsyncs exact `INTENT`, attempts
one POST, strictly validates the draft response, and writes and fsyncs
`COMMITTED`. A preflight failure creates no state and performs no POST. Any
persisted INTENT or post-attempt uncertainty remains ambiguous and cannot be
retried automatically.

All Wave 2A implementation tests are offline and fake-transport based. OAuth
success and the owner-private stored token are bounded live prerequisites from
the approved amendment, not evidence produced by these tests. The numeric-site
preflight and the single authorized draft POST remain unexecuted by the
implementation worker. Publication, formal TST, staging, release, production,
and canonical Story completion remain outside this authority.

## WordPress.com review-draft Wave 2B REST v1.1 activation

The repository owner approved the byte-exact
`WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION` handoff at SHA-256
`0a10b777ccd1e786f34890458621a21a9684feb73cee2b6808a5facefeef65ee`.
Its detached approval overlay records the exact 12,678 bytes, owner statement,
predecessor handoff hashes, `open_decisions: []`, and unchanged no-publication
limits. The approved proposal bytes remain unchanged.

Wave 2B changes only the unavailable provider transport. The exact remote
authority remains `public-api.wordpress.com:443`, the exact numeric site remains
`256699520`, and the immutable article, Source Packet, title, rendered content,
OAuth alias, journal schema, receipt schema, and publication boundary remain
unchanged. The candidate now verifies both predecessor handoffs and the Wave 2B
activation before it can reach a secret or network boundary. Its exact
operation binding is
`794cee08b70ea1762f2c78b9be9826a486ab1beec44844a9fbd013e740ee2abd`.

The no-state path performs exactly:

1. one authenticated `GET
   /rest/v1.1/sites/256699520/posts?context=edit&number=1&fields=ID`;
2. fsynced exact `INTENT`;
3. one `POST /rest/v1.1/sites/256699520/posts/new`; and
4. fsynced exact `COMMITTED` only after strict receipt validation.

The preflight accepts only HTTP 200, bounded JSON with exact top-level
`found`, `meta`, and `posts` members, a nonnegative non-boolean integer
`found`, an object `meta`, and an empty list or one exact positive-integer
`{"ID": ...}` object. It reads through EOF, retains no response value, and
stops before INTENT and POST on every refusal.

The POST uses `application/x-www-form-urlencoded` and deterministic UTF-8
quote-plus encoding of exactly ordered `title`, `content`, `status=draft`, and
`publicize=false`. The immutable candidate's exact form is 26,168 bytes with
SHA-256
`a111b07548326f8ea61888ea6cba0b402dca8bf94f56240c97118bf3701a0ef9`.
Success requires HTTP 200, positive non-boolean `ID`, and `site_ID` represented
as either the exact non-boolean integer `256699520` or the exact canonical
decimal string `"256699520"`. Every other type or string form is refused. It
also requires exact `status=draft`, exact `type=post`, a canonical-target HTTPS
`URL`, and `publicize_URLs` either absent or exactly `[]`. The canonical receipt
does not expose a provider site-ID representation. The raw body is never
persisted or rendered; only its SHA-256 enters a newly successful sanitized
receipt and COMMITTED journal.

Committed replay remains fully offline and precedes token access, preflight,
DNS, socket, and POST. An old Wave 2A INTENT or COMMITTED record carries a
different operation binding and fails closed as a mismatch; it is never
deleted, migrated, or reinterpreted. A Wave 2B post-attempt exception or
non-exact response retains INTENT and forbids automatic resubmission. No
redirect, proxy, retry, alternate route, dynamic field, publish, private-
publish, schedule, update, delete, media, or publicize control exists.

All implementation-worker verification is local and fake-transport based
unless a later section explicitly records otherwise. The handoff's bounded
v1.1 GET HTTP 200 and the later single-POST/read-only reconciliation are owner
evidence, not requests performed by this implementation worker. The one POST
has already occurred; its `CREATE_AMBIGUOUS` INTENT remains unchanged and must
not be retried. Formal TST, hosted CI, staging, publication, release,
production, revenue, and canonical ST-1703 completion remain separate and
unexecuted or unauthorized as applicable.

## WordPress.com MVP draft preparation Wave 3

The repository owner approved the byte-exact
`WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3` handoff at SHA-256
`46f43208309e139c062995adf7bae0cd522a564bd17d77d7966e76f8f51277be`
and explicitly accepted the documented residual race between the final exact
GET and application of the one POST. The separately bound content packet is
12,670 bytes with SHA-256
`aca2af51e2571a62215c600357fb8f0ee246e8891e60d6e5afbe40d8235ee681`.
The detached approval overlay authorizes implementation only. It does not
authorize credentials, a live prepare, publication, formal TST, staging,
release, or production.

Wave 3 is a detached, fail-closed, fixed-order slice for one article draft and
five page drafts. Its operation order, site, IDs, author, slugs, titles,
content hashes, routes, queries, form members, status, publicize setting, and
safety settings are immutable. The outward adapter exposes only the fixed
article GET/update and page scan/GET/create operations. There is no generic
HTTP, retry, fallback, publish, schedule, delete, trash, media, taxonomy,
settings, profile, theme, plugin, or affiliate-ingestion capability.

The exact owner-operated commands are:

```bash
make wordpresscom-prepare-mvp-drafts
make wordpresscom-preview-mvp
```

Neither target accepts a runtime parameter. Prepare first verifies the
physical repository, isolated CPython 3.14.6 launcher state, approved-base
ancestry, committed clean HEAD blobs, and the generated runtime manifest. It
then verifies every immutable handoff/content input. Before any secret,
journal, or network access, the owner must enter the exact contemporaneous TTY
affirmation that all dashboard/mobile editors, integrations, scheduled
automation, and other remote writers are quiesced until final readback. The
handoff approval and no-CAS risk acceptance do not supply that affirmation.

The generated runtime manifest is owned by
`scripts/build_wordpresscom_mvp_runtime_manifest.py`. Regenerate it only after
an approved runtime-source change and check it without writing with:

```bash
.venv/bin/python scripts/build_wordpresscom_mvp_runtime_manifest.py --check
```

Wave 3 uses only the separate owner-private
`.secrets/wordpresscom-review-draft/mvp-wave3-state` record tree and lock. It
cannot use, read, reinterpret, migrate, or alter the Wave 2 journal. Records
are sequence checked, hash chained, exclusive-created, file-fsynced, and
directory-fsynced. A durable `INTENT` consumes the operation's only POST
budget. A later process may run the one bounded GET reconciliation cycle, but
never resend that operation. Any absent, duplicate, malformed, mismatched, or
uncertain reconciliation remains ambiguous.

The article mutation requires an exact baseline GET, fsynced INTENT, a second
immediate exact baseline GET, one update POST, and an exact full-object
readback. Each page create requires a bounded exact collection scan, fsynced
INTENT, a second zero-candidate scan, one create POST, and an exact full-object
readback bound to the acknowledged ID. Existing exact placeholder objects are
reused without mutation. Author ID `283672805` must display exactly
`暮らし選びノート編集部`; a mismatch stops and Wave 3 cannot change a profile.

Preview is read-only and emits only the closed sanitized operation/base/
affiliate/manual-review schema with `publication_authority=NONE`. It may
classify three manually filled affiliate slots only after the outside-slot hash
and narrow HTML grammar pass. This does not validate rendered image pixels,
product destination legitimacy, tracking, price absence in a rendered image,
contact delivery/storage/retention, policy correctness, or rendered sharing
controls. Those remain human checks before a separately approved manual
publication.

For read-only preview only, a response refusal may now refine the existing
per-operation `reason_code` value without adding an output key. A full article
GET or existing-page full GET can report closed `FULL_GET_*_INVALID` stages for
transport, status, content type, bounded JSON, top-level keys, site ID, author
shape, discussion shape, `publicize_URLs`, identifiers, scalar field types,
target URL, or the application invariant. Author shape covers the existing
object-type and required `ID`/`name` predicates. Discussion diagnostics use
fixed value-free categories for non-object type and missing required members.
The predecessor aggregate `FULL_GET_NESTED_SHAPE_INVALID`,
`FULL_GET_DISCUSSION_SHAPE_INVALID`, and
`FULL_GET_DISCUSSION_EXTRA_KEYS` values remain stable reserved categories. The
fixed operation ID distinguishes the article from the affected page. A page
collection refusal uses the separate closed `PAGE_SCAN_*_INVALID` vocabulary
so it cannot be mistaken for the later existing-page full GET. Unknown,
missing, mutated, or context-inconsistent diagnostic state remains the generic
`RESPONSE_INVALID`.

These codes are stable and value-free. They never contain or add a response
value, provider-learned ID, URL, host/query, HTML, content, title, hash, header,
token alias, provider body, exception, or stack. The underlying exception code
and its string/repr remain the existing generic failure.

The repository owner also authorized the narrower Wave 3 read-only
`OBJECT_DRIFT` diagnostic slice. It changes only the existing preview
`reason_code` value: the operation `state`, top-level keys, base-state rules,
affiliate/manual-review fields, and `publication_authority=NONE` remain exact.
For the article it distinguishes the exact approved Wave 2 baseline, a mixed
desired/baseline profile, and each fixed identity, baseline-modified, title,
content, slug, status, type, discussion, likes, sharing, and publicize-URL
comparison. Existing pages receive the corresponding fixed page comparison
categories. The exact approved baseline is still `DRIFT`, never prepared or
ready for publication review.

The diagnostic classifier revalidates the exact bound operation, complete
content bundle, decoded remote-object invariant, identifiers, and approved
target before selecting a reason. Mixed article profiles have fixed precedence
over individual field reasons. Unknown, mutated, or internally inconsistent
diagnostic state falls back to `OBJECT_DRIFT`. Journal ambiguity/refusal,
exact/missing observations, affiliate-invalid precedence, response parsing,
prepare behavior, ports, transport, journal state, POST budget, and publication
authority do not change. The detailed values are emitted by the argument-free
read-only preview only; the prepare return path retains generic `OBJECT_DRIFT`.
No diagnostic includes a remote value, provider body, ID value, title, content,
URL, HTML, or hash, and no output key was added.

This authorization does not authorize this implementation worker to perform
the separately approved post-commit live read-only preview. That single live
preview remains pending for the integration owner after commit. It also grants
no live prepare, journal write, POST, profile/site change, publication, formal
TST/CI, staging, release, or Production authority.

## WordPress.com MVP draft preparation Wave 3A

The repository owner separately approved the exact 12,741-byte
`WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3A_OPAQUE_DISCUSSION_EXTENSIONS`
handoff at SHA-256
`1c0d50faedd3c76d18101afb1032d82da21a6daf0a01e9c687371d20519926aa`.
The detached 1,852-byte approval overlay has SHA-256
`c1002959dda0de0ba0c0535697a814fa3221fcb05c7947f543452ef99232afb0`.
Both are fixed pre-capability sources and runtime-manifest entries.

Wave 3A changes only the nested `discussion` decoder boundary. `discussion`
must still be a JSON object containing fixed `comments_open` and `pings_open`
members. Both remain actual JSON booleans, and downstream exact-state proof
still requires both to be false. Additional nested members may pass only after
the complete response has already passed the unchanged size, UTF-8,
duplicate-key, finite-number, depth, node-count, and JSON-shape checks. The
adapter does not enumerate or interpret extension names. It accesses only the
two fixed required names and drops all other nested members before constructing
`MvpRemoteObject`.

No extension name or value enters a domain field, application comparison,
preview, CLI output, journal call, persistence, hash, exception, or log.
Unknown top-level members remain rejected. Author, identity, URL, status,
content, `publicize_URLs`, likes, sharing, and every other predecessor
predicate remain unchanged. The fixed routes, methods, fields, transport,
prepare state machine, journal, INTENT/POST budget, no-resend rule,
publication authority, and all human/live/formal/release gates are unchanged.
The Wave 3A approval authorizes no live prepare, POST, profile/site change,
publication, release, or Production action.

All implementation evidence in this repository pass is local and uses fake
providers or disposable fixture paths. No live preview, prepare, OAuth,
browser, secret read, WordPress GET/POST, profile/site mutation, publication,
formal TST-021/TST-022/TST-032, hosted CI, staging, release, production, or
revenue review was executed. The exact local command results and owned-path
inventory are appended to `docs/worklogs/ST-1703.md`.

## Strict typing and current runtime maintenance

The final ST-1703 strict-typing pass makes the existing JSON boundaries,
runtime-checkable ports, immutable credential values, and journal control flow
explicit to Pyright. Exact type guards and all fail-closed validation remain in
place. OAuth and HTTP request bytes, headers, response ordering, journal
atomicity, draft-only behavior, single-attempt mutation budget, no-resend rule,
and public interfaces retain their predecessor semantics. Cross-object
credential access is limited to named immutable getters; it adds no mutable
payload or setter.

Historical Wave 1/2/3/3A handoffs and detached approvals remain byte-identical.
The active 27-path Wave 3 runtime manifest is regenerated from its owner and
keeps the approved V3 commit as a minimum ancestry/integrity anchor. Its
separate current-development fields bind repository-local maintenance to the
root standing development authorization and bind all external action authority
to `NONE`. The low-cost pilot preserves every historical manifest identity in
its historical provenance and separately validates the active current runtime
manifest; its 9,380-byte non-executable projection remains byte-identical.

The physical `/home/minami/rakuten` production launcher guard is unchanged.
Tests in an isolated linked worktree assert that literal before rebinding only
the imported test module; the unmodified shell launcher must instead refuse the
noncanonical root with its exact exit 69 boundary. No `.secrets/` content,
browser, provider call, GET/POST, journal mutation, profile/site change,
publication, formal TST/CI, staging, release, revenue review, or Production
action is authorized or executed by this maintenance pass.
