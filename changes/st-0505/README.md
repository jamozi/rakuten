# ST-0505 — Rakuten owner-local one-call smoke

Classification: `SOURCE_DERIVED_EXPLICIT_LOCAL_RAKUTEN_LIVE_SMOKE_PLAN`.
Contract revision `3.0.0` implements an installable, owner-local, explicit
Rakuten Ichiba Item Search 2026-07-01 smoke. Default activation remains
disabled. This repository revision, its tests, and its generated plan contain
no live-provider execution evidence and do not satisfy formal TST-016,
staging, release, or Production.

## Fixed request and output boundary

- The outward adapter uses only stdlib `http.client` and `ssl`, direct TLS to
  `openapi.rakuten.co.jp:443`, and path
  `/ichibams/api/IchibaItem/Search/20260701`. Proxy discovery, TLS override
  environment, redirect following, endpoint override, retry, and pagination
  are rejected or absent.
- DNS is resolved exactly once. Every returned IPv4/IPv6 candidate must be a
  well-formed public address; one loopback, private, link-local, metadata,
  multicast, reserved, scoped, mapped, or otherwise non-public candidate
  rejects the whole set before socket creation. The first fully validated
  numeric address is pinned for the sole TCP attempt without fallback, while
  TLS SNI, certificate hostname verification, and HTTP `Host` remain fixed to
  `openapi.rakuten.co.jp`.
- The blocking system resolver runs in one exec-isolated child of the already
  authenticated `/proc/self/exe`, with `-B -I -S`, a fixed helper body, minimal
  environment, closed inherited descriptors, parent-death `SIGKILL`, at most
  64 candidates, and at most 64 KiB of bounded IPC. A monotonic five-second
  deadline covers child launch through complete resolver output. Expiry,
  resolver failure, late completion, malformed output, or failed bounded reap
  closes the pipe and fails as fixed `DNS_FAILED`, `NOT_SENT`,
  `request_count=0`, with no provider metadata and no retry; a live service run
  still writes exactly one sanitized failure result when its result store is
  safe.
- One explicit invocation sends at most one GET. After all local preconditions
  pass, it sends exactly one GET with `keyword=収納`, `hits=1`,
  `page=1`, `format=json`, `formatVersion=2`, `sort=standard`, and the exact
  seven-element projection
  `count,page,first,last,hits,pageCount,affiliateUrl`.
  `applicationId` and `affiliateId` are query values; `accessKey` is sent only
  in the header named `accessKey`.
- The unchanged ST-0502 `RakutenItemSearchLiveRequestV1` remains the safe
  allowlist and zero-retry/zero-pagination predecessor. The ST-0505 report
  fingerprint binds both that policy fingerprint and the narrower wire
  projection.
- The response is capped at 2 MiB and validated as strict UTF-8 JSON. Duplicate
  keys, nonfinite numbers, excessive depth/nodes, unknown response keys,
  invalid summary cardinality, and missing/non-HTTPS `affiliateUrl` fail
  closed. Raw bodies, provider descriptions, product text, URLs, review data,
  affiliate rate, EPC/RPM, and revenue values are never reported.
- Report schema V2 records `response_sha256` over each complete bounded
  response-body byte sequence. The HTTP status line, headers, and transfer
  framing are excluded. Content-Length is parsed strictly and must match the
  observed body; chunked framing must be the sole transfer coding, and
  close-delimited EOF is the only no-length completion boundary. Malformed,
  conflicting, truncated, oversized, or otherwise incomplete reads do not
  claim a response-body digest. The body itself and all reflected provider
  material remain forbidden.
- HTTP 429 proves only `rate_classification=THROTTLED`; authentication remains
  `NOT_OBSERVED` unless a separate response establishes it.

Credentials are read only from
`.secrets/rakuten-live-smoke/credentials.v1.json`. The exact keys are
`schema_version: 1`, `application_id`, `access_key`, and `affiliate_id`.
The descriptor-bound reader requires current UID, non-symlinked ancestors,
private `0700` directories, a regular non-symlink mode-`0600` single-link
file, bounded bytes, and strict duplicate/unknown/missing/control/whitespace
validation. Two bounded reads from the same descriptor must be byte-identical,
and descriptor identity, size, modification-time, and change-time must remain
stable; credential rotation must use an atomic replacement. The reader never
creates or mutates the credential record.

The credential record is unusable without the separate owner-private
`.secrets/rakuten-live-smoke/staging-credential-binding.v1.json`. Its exact keys
are `schema_version: 1`, `environment: staging`, `credential_purpose:
DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC`, and
`credential_record_sha256`, which must equal SHA-256 of the exact credential
record bytes. The binding has the same descriptor-bound, current-UID,
non-symlink, mode-`0600`, single-link, bounded, double-read stability rules.
This repository never creates or mutates it. It must come from a separate
Operations process that establishes dedicated-test credential provenance;
self-labeling does not execute OD-015 or prove ENV-STAGING/TST-016.

Sanitized reports are atomically published mode `0600` at
`.secrets/rakuten-live-smoke/reports/<UTC-run-id>.json` from an anonymous
`O_TMPFILE` inode. A failed post-publication check rolls the target back. If
safe rollback itself fails, the writer attempts a fixed value-free mode-`0600`
`<UTC-run-id>.recovery-required` marker to record the recovery need. Report-store
failure retains the already-observed request/auth/schema/rate/affiliate/hash
metadata instead of falsely returning a zero request count.
Any recovery marker or abandoned preflight name blocks doctor, live preflight,
and every subsequent report publication until owner-side recovery.

## Independently installed entry

Repository scripts are not allowed to read credentials directly. Every install
and reinstall first binds the named stage through fd 4 with the root-owned
static BusyBox entry. Before hashing or parsing it, the outer gate requires the
opened stage and named path to identify the same current-UID, regular,
single-link, bounded, non-group/world-writable inode. Only after this check does
it authenticate the exact stage bytes. Only that authenticated static stage may
validate and start the exact root-owned `/usr/bin/python3.10` binary. Before
the dynamic exec it validates the fixed loader and `ld.so` configuration, the
root-owned OS runtime metadata closure for native libraries and stdlib, the
absence of loader/Python path shadows, and the exact installer bytes through
fd 6. Metadata trust here is deliberately not a byte-exact stdlib claim: the
root-owned OS runtime and package manager are trust anchors, root compromise is
out of scope, and any pinned interpreter or loader-configuration drift fails
closed pending review.

The authenticated Python installer then installs the exact reviewed payload
outside the repository. It uses a staged owner-private tree, file/directory
fsync, `renameat2(RENAME_NOREPLACE)`, inode verification, exact payload hashes,
directory mode `0700`, launcher mode `0500`, and payload/manifest mode `0400`.

```bash
/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/rakuten/scripts/rakuten_live_smoke_runtime_install.sh; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; u=$(/usr/bin/busybox id -u 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; case "$u" in ""|*[!0-9]*) /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; fm=$(/usr/bin/busybox stat -Lc "%d %i %f %u %a %h %s" /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; nm=$(/usr/bin/busybox stat -c "%d %i %f %u %a %h %s" -- "$p" 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; [ "$fm" = "$nm" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; set -- $fm; [ "$#" -eq 7 ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; case "$1:$2:$3:$4:$5:$6:$7" in *[!0-9a-f:]*) /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; v=$((0x$3)); [ $((v & 0xf000)) -eq 32768 ] && [ "$4" -eq "$u" ] && [ $((v & 18)) -eq 0 ] && [ "$6" -eq 1 ] && [ "$7" -ge 1 ] && [ "$7" -le 2097152 ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; [ "$h" = "9effd085052570cf943f311b012c6dcf7ac26c2514182513c1f52d33ca88d549  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; exec /usr/bin/busybox sh /proc/self/fd/4'
```

Direct repository-path execution of the Python installer refuses before
runtime mutation. Install and reinstall do not open, stat, list, read, write,
or mutate `.secrets`, the credential record, staging binding, or reports, even
when those paths already exist. Maintenance performs no network operation and
never chains doctor or run. An exact existing bundle is fully validated before
returning `ALREADY_INSTALLED`; a distinct reviewed bundle is installed
side-by-side. Neither path migrates, rebinds, or deletes credential, binding,
or report material.

Authenticated installation is credential-blind owner-local maintenance only.
Even a successful install proves only exact local-runtime installation: it
does not prove credential availability or provenance, resolve OD-015, grant
live-provider authority, execute a provider call or TST-016, establish
ENV-STAGING, accept or validate ST-0505, release, or reach Production. This
implementation does not run that installer; installed-runtime status is
`NOT_EXECUTED` and `NOT_EVIDENCED`. Disposable tests do not elevate that state.

The authoritative entries are the following two complete, fixed commands. The
root-owned static BusyBox process clears the inherited environment and verifies
the exact installed launcher bytes before that launcher body executes:

```bash
/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/.local/share/raos/rakuten-live-smoke/runtime/94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d/bin/rakuten-live-smoke; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; [ "$h" = "9deabbf7dff82e43b87a793a27b0c7f0d7371e97559755484f0c5cba9ddeabed  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; exec "$p" doctor'

/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/.local/share/raos/rakuten-live-smoke/runtime/94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d/bin/rakuten-live-smoke; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; [ "$h" = "9deabbf7dff82e43b87a793a27b0c7f0d7371e97559755484f0c5cba9ddeabed  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; exec "$p" run'
```

The outer static, root-owned `/usr/bin/busybox` stage zero authenticates the
launcher SHA-256 before executing it. The authenticated launcher validates
secure ancestry, exact launcher/CLI/Python metadata, the CLI and Python hashes,
rejects `pyvenv.cfg`, other path-configuration or RPATH loader shadows, and
rejects unowned, non-regular, or group/world-writable stdlib material. It runs
Python with `-B -I -S` and passes a descriptor for the authenticated launcher.
The Python entry refuses direct payload invocation without that descriptor,
rejects every unmanifested runtime path (including `__pycache__` and package
initializers), and verifies the manifest and every installed payload through
descriptor-relative `O_NOFOLLOW` reads before importing RAOS code or
constructing the credential reader. Repository drift and other-UID writes
therefore cannot change the credential-bearing entry. The current-UID managed
Python/stdlib tree is trusted after the documented metadata and writable-bit
checks; same-UID replacement, hash-to-exec race, or deliberate stage-zero
descriptor forgery is explicitly out of scope.

A bare invocation of the installed launcher refuses before constructing the
credential reader unless it inherits the authenticated outer-gate descriptor
on fd 4. Direct Python payload invocation likewise refuses without the
launcher descriptor on fd 3.

Repository Make entrypoints are intentionally not provided. A writable
Makefile is outside the bootstrap authority for runtime installation and
secret-bearing execution; the complete reviewed direct install, doctor, and
live commands above are the only documented entries.
Doctor checks installed-runtime, staging-binding and credential-record
structure, and report-store metadata only; it checks report metadata before
reading the binding or credentials, does not construct a transport, and
performs no network or filesystem mutation. It is not provider auth/IP/schema
proof and does not prove the filesystem's actual anonymous publication
operation. Run first proves the exact anonymous inode,
link, identity, rollback, and directory-fsync path, before reading credentials
or attempting the GET, and always requires a fresh explicit invocation. In
particular, HTTP 403/authentication/IP mismatch is never retried; provider-side
configuration must be corrected before another owner invocation.

## Evidence boundary

The owner-local entry is a disabled, non-formal, non-attesting diagnostic
surface only. This artifact grants no live-provider execution authority. No
result from it, including `LIVE_SMOKE_PASS`, executes or satisfies TST-016 or
advances ST-0505 acceptance, adapter `VALIDATED` status, ENV-STAGING, release,
or Production. Formal TST-016 remains an Operations-owned ENV-STAGING execution
using dedicated test credentials backed by scoped account/permission/secret
evidence and its required immutable evidence record.

OD-015 remains `EXTERNAL_EVIDENCE_REQUIRED`, blocking, unresolved, and
default-safe as `Recorded fixtureのみ`. The local fake tests do not read the
owner credential record or make a provider request. Observation defaults,
formal TST-016, live auth/schema/rate, staging, release, and Production all
remain `NOT_EXECUTED`; Story acceptance and Production eligibility remain
false.

## Owner generation

Generated JSON and manifest output are owned only by the builder:

```bash
python3 scripts/build_st0505_rakuten_live_smoke_reference_plan.py
python3 scripts/build_st0505_rakuten_live_smoke_reference_plan.py --check
```

## Separate owner-local provider production-read integration

`rakuten-owner-local` is a second, side-by-side installed runtime. It does not
replace, migrate, invoke, or change the staging-bound `rakuten-live-smoke`
runtime above. The word `production` in the credential profile means only that
the credential belongs to Rakuten's provider-production API. It does not select
RAOS Production, ENV-STAGING, release authority, or formal TST-016.

The credential-blind installer publishes a reviewed versioned bundle only at
`/home/minami/.local/share/raos/rakuten-owner-local/runtime/fd23f88bb61d8919015602e48bc5c10b5df06d4c9dff4986ff513e4500249d93/`.
No repository Make target is an authoritative secret-bearing entry. The exact
static-BusyBox install and invocation commands are emitted by the generated
contract after the final payload hashes are fixed. Direct repository Python,
installer, or launcher execution refuses before prompt, credential, result, or
network access.

The generated plan binds launcher SHA-256
`27aa51a680eac393c304da443a82b6930a956c21913a53827ccf6584a2c1c47d`,
installer SHA-256
`e25b742f76904f8c50db9439bc02f435bdf8076068ea0e00a0746b69bdaf60ef`,
and install-stage SHA-256
`4745a3b74b307c16c542012d3e44526ea80e70915ea12e1c51874df6da9cacea`.
Its fixed setup, rotate, doctor, list, and smoke commands authenticate fd 4
before the installed launcher body. Request-file invocation uses the same gate,
with the selected API and absolute path passed only as positional arguments;
shell interpolation of request material is forbidden.

The generated plan exposes custom request invocation as a structured argv
template, not as a copy-and-edit shell command. Callers replace only the two
declared array elements for the closed API name and owner-selected absolute JSON
path, then invoke that argv directly. The gate rejects unrendered placeholders,
unknown APIs, relative paths, or extra values before the launcher body; values
are never concatenated into the shell program and `eval` is forbidden.

The installed command surface is closed:

- `setup` creates the absent exact-schema credential record after hidden,
  repeated `/dev/tty` entry and a hidden confirmation.
- `rotate` atomically replaces one already-valid credential record after the
  same hidden entry flow.
- `doctor` checks result-store metadata before reading and validating the
  credential record and never constructs a network transport.
- `list-apis` emits only the fixed registry containing `item-search` and
  `product-search`.
- `request --api <item-search|product-search> --request-file <absolute-json>`
  performs at most one reviewed read request.
- `smoke --api <item-search|product-search>` uses fixed keyword `収納`, hits 1,
  page 1, and standard sort for one request.

Credentials exist only at
`.secrets/rakuten-owner-local/credentials.v1.json`. Exact keys are
`schema_version: 1`, `profile: OWNER_LOCAL_RAKUTEN_PRODUCTION_API`,
`application_id`, `access_key`, and `affiliate_id`. Private ancestors are
mode `0700`; the regular single-link file is mode `0600`. Descriptor-relative
`O_NOFOLLOW` reads reject symlinks, owner/mode/type/link drift, oversized or
unstable bytes, duplicate/unknown/missing keys, controls, and edge whitespace.
Setup never overwrites; rotation uses an atomic replacement and directory
fsync. Secret values never appear in argv, environment, stdout, stderr,
exceptions, repr, result files, generated files, or install metadata.

Item request V1 wraps the unchanged ST-0502
`RakutenItemSearchLiveRequestV1`. It requires exactly one of keyword, genre,
item, or shop, page 1, hits 1 through 30, and only the existing safe sorts and
elements. Review aggregates and affiliate-rate fields remain excluded from the
normalized result even though the unchanged predecessor element projection may
include other inert product-description fields. For an exact `itemCode` or
`shopCode` request, every returned Item record must contain the exact selected
identity; a different valid provider identity fails as `RESULT_MISMATCH` before
credential-reflection inspection. Empty results remain valid and fields that
were not selected are not identity constraints. Product request V1 permits a
keyword with optional genre, a genre alone, or one exclusive product ID/code;
it fixes page 1 and allows only standard sort. Product review-derived sort and
review aggregates are unavailable. For an exclusive `productId` or
`productCode` request, every returned record must contain the exact selected
identity; a different valid provider identity fails as `RESULT_MISMATCH`.

Both adapters fix `openapi.rakuten.co.jp:443`, their reviewed versioned paths,
GET, format JSON/version 2, and exact elements. `applicationId` and
`affiliateId` are query values. The access credential is sent only in the
header whose name is `accessKey`; it is never a query value. Proxy discovery,
TLS override environment, redirects, retries, pagination follow-ups,
concurrency, arbitrary endpoints/headers/parameters, and IP fallback are
rejected. Every resolved candidate must be a public address before the first
candidate is pinned for the sole TCP attempt. TLS SNI, certificate hostname
verification, and HTTP host remain the fixed Rakuten hostname.

Complete bodies are bounded to 2 MiB and validated as strict UTF-8 JSON with
duplicate-key, nonfinite-number, depth, node, summary, collection, and field
checks. Because page is fixed to 1, an empty collection requires zero
`count`, `pageCount`, `first`, and `last`; a non-empty collection requires
`count` at least its cardinality, `pageCount` exactly equal to
`min(ceil(count / hits), 100)`, `first=1`, and `last` equal to the returned
cardinality. Product Search's official page does not unambiguously name its
format-version-2 collection envelope, so the adapter recognizes only the two
reviewed literal envelope names documented in its tests and treats any other
shape as schema drift; this does not permit an arbitrary schema fallback.
Item Search alone also permits the documented optional top-level carrier. If
present, it must be exact integer `0`; `bool`, nonzero integers, and every
non-integer fail closed. The carrier is never normalized or persisted. Product
Search and every root member other than its existing reviewed keys remain
unchanged and fail as unrecognized root material.

The current official Item Search 2026-07-01 documentation presents a lowercase
`items` collection containing flat format-version-2 records. The Item adapter
also accepts the exact compatibility alias `Items`, but requires exactly one of
`items` or `Items`; absence, both aliases, approximate casing, and every other
root member fail closed under the existing collection-detail precedence.
Nested `Item` or `item` record wrappers remain invalid. This one-alias
compatibility boundary was selected after sanitized owner-local evidence
reported HTTP 200, body size 5771, and `COLLECTION_KEY_INVALID`; because no raw
body was retained, that evidence does not prove which provider member was
observed. Both accepted inputs normalize and persist only canonical lowercase
`items`, and the source alias is never evidence. Product Search is unchanged.

The DNS deadline is complete before any socket is constructed or any
credential-bearing request is sent. The existing 20-second per-operation socket
timeout remains an upper bound.
After the sole GET is sent, a separate monotonic 20-second absolute deadline
covers response headers through the complete Content-Length or chunked body,
or through EOF for a close-delimited body. The response socket recomputes the
positive remaining budget before every raw `recv_into`, including header,
chunk-header, trailer, and body parsing, and the bounded body loop uses only
`HTTPResponse.read1`. Continuous trickling therefore cannot refresh the
budget indefinitely. Deadline expiry is the fixed sanitized `TIMEOUT` with
`OUTCOME_AMBIGUOUS` and `request_count=1`; no partial body, status, byte count,
digest, normalized record, or credential-bearing material is persisted.

Results are atomically and exclusively published mode `0600` under
`.secrets/rakuten-owner-local/results/<UTC-run-id>.json`. They contain the
request fingerprint, timestamps, fixed endpoint/version, HTTP/body metadata,
SHA-256 of the complete bounded raw response bytes, precise request disposition,
summary, and allowlisted normalized records. Raw bodies/headers, provider error
descriptions, captions, review bodies or aggregates, affiliate rate, EPC, RPM,
revenue, the application ID, the access key, and the affiliate ID outside the
three exact validated public-link fields are forbidden. The affiliate ID may
remain only within those field-local public affiliate links described below.
Stored provider fields are always classified `UNTRUSTED_PROVIDER_DATA`. The closed
`RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V3` object always contains the same
exact keys for success and failure. Success persists all six validated summary
scalars in the in-memory result-object order `count`, `page`, `first`, `last`,
`hits`, `pageCount`;
failure retains those six keys with `null` values, including sanitized
credential-reflection failures. Result files are compact UTF-8 JSON with
lexicographically sorted keys and one trailing LF. Existing V1 and V2 evidence
remain immutable and are never rewritten. V3 keeps the always-present nullable
`validation_stage_code` and adds one always-present nullable
`validation_detail_code`; this side-by-side schema change makes no
deployed-result migration or backward-compatibility claim. If exact
`timezone.utc`, fold-0 start
and terminal wall-clock values show
the terminal observation earlier than `started_at`, `finished_at` is clamped to
`started_at`. If terminal clock sampling raises after the attempt, the already
sampled `started_at` is reused. Success, received provider failure, and
outcome-ambiguous evidence therefore retain their original disposition, request
count, and response metadata and still reach the one bounded result write.
Invalid values returned by the clock are not compared or clamped and retain the
existing fixed `INVALID_ARGUMENT` result-envelope validation. Every returned Item record requires a
non-null, non-empty, bounded UTF-8 `itemCode` and `itemName`; every returned
Product record requires the same shape for `productCode` and `productId`.
`shopCode`, `shopName`, and `productName` retain their existing optional and
nullable behavior unless a field is the selected exact selector. Mandatory-key
presence is checked before exact-selector identity; a valid-but-different exact
selector remains `RESULT_MISMATCH`, while an invalid mandatory text shape is
`RESPONSE_SCHEMA_DRIFT` before success or persistence.

Every returned Item record also requires a non-null strict HTTPS `itemUrl`, and
every returned Product record requires a
non-null strict HTTPS `productUrlPC`; missing, null, empty, non-string, or
non-HTTPS values fail as `RESPONSE_SCHEMA_DRIFT` before success or persistence.
The existing nullable scalar `affiliateUrl` and Product image URL values remain
nullable; URL-list values remain non-null tuples whose members are HTTPS.
All normalized URL positions also reject embedded Unicode whitespace, Unicode
control and format characters, raw backslashes, malformed percent escapes,
userinfo, fragments, invalid IDNA DNS labels, and invalid bracketed IPv6
syntax. Valid international or punycode hostnames, IPv4, bracketed IPv6,
optional ports, paths, and queries remain supported; this syntax check does not
expand the transport SSRF policy.

Field presence is checked before exact-selector identity, then mandatory text
and URL value shape are checked before credential reflection. After result
identity and request binding but before a success envelope or result write,
every normalized record string and string-list member is inspected in raw UTF-8
and after one percent-decoding pass. The application ID and access key remain
sensitive in every such position. The affiliate ID remains sensitive in every
position except the exact, already HTTPS-validated provider affiliate-link URL
fields: Item Search `affiliateUrl` and `itemUrl`, and Product Search
`affiliateUrl`. Product `productUrlPC`, text fields, image URLs, URL-list
members, unknown fields, and near-case field names receive no exemption. This
is a field-local allowance for public link material, not a general
declassification of the affiliate ID, and URL validation always runs first.

The current official Item Search source at
<https://webservice.rakuten.co.jp/documentation/ichiba-item-search> states that
`affiliateUrl` is returned only when `affiliateId` is supplied and that
`itemUrl` equals `affiliateUrl` in that case. Older official documentation also
describes affiliate-link construction as including the affiliate ID. Separately,
sanitized owner-local evidence records exactly one HTTP 200 Item request, body
size 5771, response SHA-256
`833e539c890ce874f04b7b9201abca1306e1d2b1fc105c99529c587883afdc03`,
zero retry and pagination, and Result V3 failure at
`CREDENTIAL_REFLECTION`. No raw body or observed field was retained, so the
root-cause classification is an official-spec conflict plus sanitized stage
evidence, not proof that a particular response field contained the affiliate
ID.

The six schema- and relationship-validated summary integers and every non-text
normalized value already accepted by its field schema are not converted to text
for credential comparison; typed scalar equality alone is not evidence of
reflected credential bytes. HTTP status, body byte count, response hash,
request count, and fixed identifiers remain required local evidence metadata
rather than reflected provider text. A non-exempt inspected-text match fails
with the fixed `RESPONSE_SCHEMA_DRIFT` code while retaining only complete
HTTP/body/SHA metadata and `request_count=1`; the matched value, summaries, and
normalized records are not persisted.

Response-validation failures retain their existing generic `diagnostic_code`
and fixed CLI output. V3 retains the closed, value-free
`validation_stage_code`: `SUMMARY_SHAPE`, `COLLECTION_SHAPE`, `RECORD_SHAPE`,
`EXACT_SELECTOR`, `MANDATORY_TEXT`, `URL`, or `CREDENTIAL_REFLECTION`. Success
and failures outside these validation boundaries store `null`. The stage never
contains a provider field name, record index, expected or actual value, raw body,
header, exception detail, or credential material. Validation remains fail-closed
in this order: collection envelope, summary, record shape, exact selector,
mandatory text, URL, then credential reflection. An exact-selector identity
mismatch retains `RESULT_MISMATCH`; all other listed validation refusals retain
`RESPONSE_SCHEMA_DRIFT`. Available response metadata and `request_count=1` are
preserved while provider results and summaries remain absent on failure.
`validation_detail_code` is non-null if and only if the generic diagnostic is
`RESPONSE_SCHEMA_DRIFT` and the stage is `COLLECTION_SHAPE`. Its closed values
are `ROOT_NOT_OBJECT`, `COLLECTION_KEY_INVALID`,
`ROOT_MEMBER_UNRECOGNIZED`, `COLLECTION_NOT_ARRAY`, and
`OPTIONAL_ROOT_MEMBER_VALUE_INVALID`, in that precedence order. No value names
the observed key or contains a provider value, index, expected/actual material,
body, header, exception detail, or credential. Success, non-validation failures,
and every other validation stage store `null`.
Every returned record completes each stage before any record enters the next,
so provider record order cannot make an earlier URL defect hide a later
exact-selector or mandatory-text refusal.
This diagnostic narrows only where validation stopped; it does not accept a new
provider shape, infer a missing official schema rule, or change the existing
fail-closed boundary.

Every local result is `OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE`. Implementation
and fake tests do not execute a real credential read, provider call, formal
TST-016, ENV-STAGING, release, or RAOS Production. OD-015 remains blocking and
unresolved with safe default `RECORDED_FIXTURE_ONLY`; the existing recorded
ST-0502 service remains unchanged.
